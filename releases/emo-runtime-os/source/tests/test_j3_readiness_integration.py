"""Phase J3 — Production Readiness Integration Tests.  # LAW-3 LAW-5 LAW-8 LAW-11 LAW-20 LAW-21 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

5 test groups covering Recovery Guards (G-C1–G-C3), Load Determinism (G-D1),
Trace Correlation, Certification Safety, and Stability Validation.

Ref: artifacts/design/j3/protocols/01_readiness_protocols.py
Ref: artifacts/design/j3/03_chaos_recovery_machine.md
Ref: Canon LAW 3, 5, 8, 11, 20-22, RULE 1-5
"""

from __future__ import annotations

import asyncio
import hashlib
import time

import pytest

from core.readiness.chaos_injector import ChaosInjector
from core.readiness.load_orchestrator import LoadOrchestrator
from core.readiness.stability_validator import StabilityValidator
from core.readiness.certification_gate import CertificationGate
from core.readiness.readiness_state_machine import (
    ReadinessStateMachine,
    ChaosTransition,
    LoadTransition,
    CertificationGateTransition,
)
from core.readiness.trace_correlator import ReadinessTraceCorrelator

TRACE_ID = "rdns_test_integration_001"


# ── Helpers ────────────────────────────────────────────────────


def _sm() -> ReadinessStateMachine:
    return ReadinessStateMachine(strict_readiness_mode=True)


def _tc() -> ReadinessTraceCorrelator:
    return ReadinessTraceCorrelator()


def _ci() -> ChaosInjector:
    sm = _sm()
    tc = _tc()
    return ChaosInjector(sm, tc, TRACE_ID)


def _lo() -> LoadOrchestrator:
    return LoadOrchestrator(_sm(), _tc())


def _sv() -> StabilityValidator:
    return StabilityValidator()


def _cg() -> CertificationGate:
    return CertificationGate(_sm())


# ══════════════════════════════════════════════════════════════════
# Group 1: TestRecoveryGuardEnforcement (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestRecoveryGuardEnforcement:
    """G-C1–G-C3: Recovery Guards prevent certification without integrity + recovery."""

    def test_chaos_injector_returns_expected_recovery_sec(self) -> None:
        result = asyncio.run(_ci().inject_network_partition(
            target_service="postgres_primary",
            duration_sec=30.0,
            readiness_trace_id=TRACE_ID,
        ))
        assert result["expected_recovery_sec"] == 45.0
        assert result["trace_id"] == TRACE_ID
        assert result["fault_type"] == "network_partition"

    def test_chaos_injector_restore_baseline(self) -> None:
        ci = _ci()
        inj = asyncio.run(ci.inject_network_partition("redis_cache", 10.0, TRACE_ID))
        result = asyncio.run(ci.restore_baseline(inj["injection_id"], TRACE_ID))
        assert result["restored"] is True
        assert result["state_after"]["status"] == "healthy"

    def test_kill_worker_returns_worker_id(self) -> None:
        result = asyncio.run(_ci().kill_worker("worker_01", TRACE_ID, graceful=False))
        assert result["worker_id"] == "worker_01"
        assert result["fault_type"] == "worker_failure"
        assert result["expected_recovery_sec"] == 15.0

    def test_simulate_db_failover_promotes_replica(self) -> None:
        result = asyncio.run(_ci().simulate_db_failover(
            "pg_primary", TRACE_ID, failover_type="primary_loss",
        ))
        assert result["promoted_replica"] == "pg_primary_replica_1"
        assert result["expected_recovery_sec"] == 60.0

    def test_stability_validator_checks_integrity(self) -> None:
        result = asyncio.run(_sv().check_data_integrity_post_chaos(
            "scenario_1", TRACE_ID,
            integrity_checks=["row_count", "checksum", "constraint"],
        ))
        assert result["integrity_verified"] is True
        assert result["checks_passed"] == 3


# ══════════════════════════════════════════════════════════════════
# Group 2: TestLoadDeterminism (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestLoadDeterminism:
    """G-D1: Load determinism and oscillation detection."""

    def test_generate_concurrent_dags_returns_dags(self) -> None:
        result = asyncio.run(_lo().generate_concurrent_dags(
            count=10, readiness_trace_id=TRACE_ID,
        ))
        assert result["submitted_count"] == 10
        assert len(result["dag_ids"]) == 10
        assert result["trace_id"] == TRACE_ID

    def test_apply_cpu_pressure(self) -> None:
        result = asyncio.run(_lo().apply_resource_pressure("cpu", 0.8, TRACE_ID))
        assert result["pressure_type"] == "cpu"
        assert result["intensity"] == 0.8

    def test_measure_p99_latency_returns_metrics(self) -> None:
        result = asyncio.run(_lo().measure_p99_latency(
            sample_size=100, readiness_trace_id=TRACE_ID, duration_sec=30.0,
        ))
        assert result["p50_ms"] > 0
        assert result["p99_ms"] > 0
        assert result["sample_count"] == 100

    def test_detect_oscillation_flags_unstable(self) -> None:
        unstable = [100.0, 200.0, 100.0, 250.0, 90.0, 300.0, 80.0, 350.0, 70.0]
        result = asyncio.run(_lo().detect_oscillation(unstable, TRACE_ID, threshold=0.3))
        assert result["oscillation_detected"] is True
        assert result["peak_count"] >= 3

    def test_detect_no_oscillation_on_stable(self) -> None:
        stable = [150.0] * 20
        result = asyncio.run(_lo().detect_oscillation(stable, TRACE_ID, threshold=0.3))
        assert result["oscillation_detected"] is False


# ══════════════════════════════════════════════════════════════════
# Group 3: TestTraceCorrelation (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestTraceCorrelation:
    """readiness_trace_id propagates across all J3 layers."""

    def test_trace_generation_and_format(self) -> None:
        tc = _tc()
        tid = tc.generate_readiness_trace_id("sess_1", "scenario_1")
        assert tid.startswith("rdns_")
        assert len(tid) >= 30

    def test_full_trace_chain_preserved(self) -> None:
        tc = _tc()
        tid = tc.generate_readiness_trace_id("sess_1", "scenario_1")
        tc.propagate_to_chaos(tid, "inj_001")
        tc.propagate_to_load(tid, "prof_001")
        tc.propagate_to_stability(tid, "m_001")
        tc.propagate_to_certification(tid, "rpt_001")
        tc.propagate_to_f4(tid)
        chain = tc.trace_chain(tid)
        assert chain["layers"]["chaos_injector"] == "inj_001"
        assert chain["layers"]["load_orchestrator"] == "prof_001"
        assert chain["layers"]["stability_validator"] == "m_001"
        assert chain["layers"]["certification_gate"] == "rpt_001"
        assert "f4_observability" in chain["layers"]

    def test_trace_chain_unknown_returns_empty(self) -> None:
        assert _tc().trace_chain("unknown") == {}

    def test_correlation_for_specific_layer(self) -> None:
        tc = _tc()
        tid = tc.generate_readiness_trace_id("s1", "sc1")
        tc.propagate_to_chaos(tid, "inj_001")
        assert tc.correlation_for(tid, "chaos_injector") == "inj_001"
        assert tc.correlation_for(tid, "load_orchestrator") == ""

    def test_multiple_traces_independent(self) -> None:
        tc = _tc()
        t1 = tc.generate_readiness_trace_id("s1", "sc1")
        t2 = tc.generate_readiness_trace_id("s2", "sc2")
        tc.propagate_to_chaos(t1, "inj_1")
        tc.propagate_to_chaos(t2, "inj_2")
        assert tc.correlation_for(t1, "chaos_injector") == "inj_1"
        assert tc.correlation_for(t2, "chaos_injector") == "inj_2"


# ══════════════════════════════════════════════════════════════════
# Group 4: TestCertificationSafety (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestCertificationSafety:
    """CertificationGate blocks when guards fail."""

    def test_load_canon_baseline(self) -> None:
        result = asyncio.run(_cg().load_canon_baseline("canon/baseline/v1.json", TRACE_ID))
        assert result["baseline_loaded"] is True
        assert result["baseline_version"] == "j3_v1.0"

    def test_run_validation_suite(self) -> None:
        result = asyncio.run(_cg().run_validation_suite({"compliance_pct": 100.0}, TRACE_ID))
        assert result["suite_complete"] is True
        assert result["checks_passed"] == 5

    def test_compute_final_score_grade_a(self) -> None:
        result = asyncio.run(_cg().compute_final_score({
            "chaos_pass": True,
            "load_pass": True,
            "integrity_pass": True,
            "canon_compliance": True,
            "p99_ms": 120.0,
            "oscillation_detected": False,
            "rollback_safe": True,
        }, TRACE_ID))
        assert result["grade"] == "A"
        assert result["certified"] is True
        assert result["final_score"] == 1.0

    def test_compute_final_score_grade_f(self) -> None:
        result = asyncio.run(_cg().compute_final_score({
            "chaos_pass": False,
            "load_pass": False,
            "integrity_pass": False,
            "canon_compliance": False,
            "p99_ms": 999.0,
            "oscillation_detected": True,
            "rollback_safe": False,
        }, TRACE_ID))
        assert result["grade"] == "F"
        assert result["certified"] is False
        assert "data_integrity_failed" in result["blocked_by"]

    def test_compute_final_score_g3_blocks_on_integrity_pass_but_p99_high(self) -> None:
        result = asyncio.run(_cg().compute_final_score({
            "chaos_pass": True,
            "load_pass": True,
            "integrity_pass": True,
            "canon_compliance": True,
            "p99_ms": 999.0,
            "oscillation_detected": False,
            "rollback_safe": True,
        }, TRACE_ID))
        assert result["grade"] == "F"
        assert result["certified"] is False
        assert "G-C3" in result["blocked_by"]

    def test_freeze_production_snapshot(self) -> None:
        result = asyncio.run(_cg().freeze_production_snapshot(
            {"grade": "A", "final_score": 1.0, "certified": True}, TRACE_ID,
        ))
        assert result["frozen"] is True
        assert result["snapshot_id"].startswith("snap_")


# ══════════════════════════════════════════════════════════════════
# Group 5: TestStabilityValidation (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestStabilityValidation:
    """StabilityValidator numerical correctness."""

    def test_evaluate_stable_throughput(self) -> None:
        stable = [100.0, 102.0, 101.0, 99.0, 100.0, 101.0, 100.0, 99.5, 100.5, 101.0]
        result = asyncio.run(_sv().evaluate_throughput_stability(
            stable, TRACE_ID, stability_threshold=0.15,
        ))
        assert result["stable"] is True
        assert result["coefficient_of_variation"] < 0.15

    def test_evaluate_unstable_throughput(self) -> None:
        unstable = [100.0, 200.0, 50.0, 300.0, 30.0, 400.0, 20.0]
        result = asyncio.run(_sv().evaluate_throughput_stability(
            unstable, TRACE_ID, stability_threshold=0.15,
        ))
        assert result["stable"] is False

    def test_verify_rollback_safety(self) -> None:
        result = asyncio.run(_sv().verify_rollback_safety("inj_001", TRACE_ID))
        assert result["trace_id"] == TRACE_ID

    def test_publish_readiness_report(self) -> None:
        report = {
            "chaos_pass": True,
            "load_pass": True,
            "integrity_pass": True,
            "canon_compliance": True,
            "final_score": 0.96,
            "grade": "A",
        }
        result = asyncio.run(_sv().publish_readiness_report(report, TRACE_ID))
        assert result["published"] is True
        assert result["report_id"].startswith("rpt_")
        assert "readiness/reports/" in result["storage_ref"]
